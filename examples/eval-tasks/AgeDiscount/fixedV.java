public class fixedV {
    // reference fix: 65 itself is a senior age, as before
    public static double snippet(int price, int age) {
        int pay = 0;
        boolean child = age < 12;
        boolean senior = age >= 65;
        pay = price;
        if (child || senior) {
            pay = price / 2;
        }
        return pay;
    }
}
