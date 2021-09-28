const transferToDDG = () => {
    let content = document.querySelector('input.searchField').value;
    window.open(`https://duckduckgo.com/?t=ffab&q=${content}`, '_self')
}

const postLoad = () => {
    const clockEle = document.querySelector('.clock');
    const docTitle = document.querySelector('title');

    const updateTime = () => {
        // SECTION: Clock
        let now = new Date();
        let times = [now.getHours(), now.getMinutes(), now.getSeconds()];
        let newTimes = [];
        times.forEach(time => {newTimes.push(String(time).padStart(2, '0'))})
        clockEle.innerHTML = newTimes.join(':');

        //SECTION: Title Greeting
        let hour = now.getHours();
        let greetTime;
        if (hour < 12) {
            greetTime = 'Morning';
        } else if (hour >= 12 && hour <=18) {
            greetTime = 'Afternoon';
        } else {
            greetTime = 'Evening';
        }
        docTitle.innerHTML = `Good ${greetTime}, ${username}`;
    }

    const delegateSubmission = (event) => {
        if (event.keyCode === 13) {
            transferToDDG();
        }
    }


    document.addEventListener('keydown', delegateSubmission);
    setInterval(updateTime, 1000);
    updateTime();
}

document.addEventListener('DOMContentLoaded', postLoad);
